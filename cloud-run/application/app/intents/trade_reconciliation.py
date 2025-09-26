from google.cloud.firestore_v1 import DELETE_FIELD
from google.cloud.firestore_v1.transaction import transactional_async
from ib_insync import Contract, util
import asyncio

from intents.intent import Intent

@transactional_async
async def _update_holdings_and_remove_open_order_async(transaction, db, holdings_doc_ref, order_doc_ref, contract_id, quantity):
    """Atomically updates holdings and removes the corresponding open order document."""
    holdings_snapshot = await holdings_doc_ref.get(transaction=transaction)
    holdings = holdings_snapshot.to_dict() or {}
    current_position = holdings.get(str(contract_id), 0)
    new_position = current_position + quantity

    if new_position == 0:
        transaction.update(holdings_doc_ref, {str(contract_id): DELETE_FIELD})
    else:
        transaction.update(holdings_doc_ref, {str(contract_id): new_position})
    
    transaction.delete(order_doc_ref)

class TradeReconciliation(Intent):

    def __init__(self):
        super().__init__()

    async def _core(self):
        self._env.logging.info('Running async trade reconciliation...')

        open_trades, fills, ib_portfolio = await asyncio.gather(
            self._env.ibgw.reqOpenTradesAsync(),
            self._env.ibgw.reqFillsAsync(),
            self._env.ibgw.reqPortfolioAsync()
        )

        self._activity_log.update(openOrders=[
            {
                'contract': t.contract.nonDefaults(),
                'orderStatus': t.orderStatus.nonDefaults(),
                'log': util.tree(t.log)
            } for t in open_trades
        ])

        reconciliation_tasks = [self._reconcile_one_fill(fill) for fill in fills]
        processed_fills = await asyncio.gather(*reconciliation_tasks)
        
        self._activity_log.update(fills=[f for f in processed_fills if f])
        self._env.logging.info(f'Processed {len(self._activity_log["fills"])} fills.')

        await self._verify_holdings(ib_portfolio)

        return self._activity_log

    async def _reconcile_one_fill(self, fill):
        contract_id = fill.contract.conId
        order_doc_ref = None
        order_data = None

        # Find the corresponding open order in Firestore
        query = self._env.db.collection(f'positions/{self._env.trading_mode}/openOrders').where('permId', '==', fill.execution.permId)
        async for doc in query.stream():
            order_doc_ref = doc.reference
            order_data = doc.to_dict()
            break

        if not order_doc_ref:
            return None # Order not found, might be from a manual trade

        side = 1 if fill.execution.side == 'BOT' else -1
        quantity_in_order = sum(order_data['source'].values())

        if side * fill.execution.cumQty == quantity_in_order:
            self._env.logging.info(f"Reconciling fully filled order for {fill.contract.localSymbol}...")
            for strategy, quantity in order_data['source'].items():
                holdings_doc_ref = self._env.db.document(f'positions/{self._env.trading_mode}/holdings/{strategy}')
                await _update_holdings_and_remove_open_order_async(
                    self._env.db.transaction(), self._env.db, holdings_doc_ref, order_doc_ref, contract_id, quantity
                )
            return fill.execution.nonDefaults()
        return None

    async def _verify_holdings(self, ib_portfolio):
        self._env.logging.info('Comparing Firestore holdings with IB portfolio...')
        portfolio = {item.contract.conId: item.position for item in ib_portfolio}
        self._activity_log.update(portfolio={item.contract.localSymbol: item.position for item in ib_portfolio})
        
        holdings_consolidated = {}
        holdings_docs = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings').stream()
        async for doc in holdings_docs:
            for k, v in doc.to_dict().items():
                k = int(k)
                holdings_consolidated[k] = holdings_consolidated.get(k, 0) + v
        
        # To prevent errors on empty dicts, create a list of contract details
        contract_details_coros = [self._env.ibgw.reqContractDetailsAsync(Contract(conId=k)) for k in holdings_consolidated.keys()]
        contracts_details_list = await asyncio.gather(*contract_details_coros)
        
        # Flatten the list of lists and create a mapping from conId to localSymbol
        conid_to_symbol = {details[0].contract.conId: details[0].contract.localSymbol for details in contracts_details_list if details}

        self._activity_log.update(consolidatedHoldings={
            conid_to_symbol.get(k, k): v for k, v in holdings_consolidated.items()
        })

        if portfolio != holdings_consolidated:
            self._env.logging.warning(f'Holdings do not match -- Firestore: {holdings_consolidated}; IB: {portfolio}')
            raise AssertionError('Holdings in Firestore do not match the ones in IB portfolio.')


if __name__ == '__main__':
    from lib.environment import Environment

    env = Environment()
    env.ibgw.connect(port=4001)
    try:
        trade_reconciliation = TradeReconciliation()
        trade_reconciliation._core()
    except Exception as e:
        raise e
    finally:
        env.ibgw.disconnect()
