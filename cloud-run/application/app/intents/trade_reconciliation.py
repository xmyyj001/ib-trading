import asyncio
from google.cloud.firestore_v1.async_transaction import async_transactional
from google.cloud.firestore_v1 import DELETE_FIELD
from ib_insync import Contract, util
from intents.intent import Intent
import logging

@async_transactional
async def _update_holdings_and_remove_open_order_async(transaction, holdings_doc_ref, order_doc_ref, contract_id, quantity):
    """
    Atomically updates holdings and removes the open order document in a single transaction.
    """
    holdings_snapshot = await holdings_doc_ref.get(transaction=transaction)
    holdings = holdings_snapshot.to_dict() or {}
    current_position = holdings.get(str(contract_id), 0)
    new_position = current_position + quantity

    if new_position == 0:
        transaction.update(holdings_doc_ref, {str(contract_id): DELETE_FIELD})
    else:
        transaction.update(holdings_doc_ref, {str(contract_id): new_position})
    
    transaction.delete(order_doc_ref)
    logging.info(f"Transaction: Updated holdings for conId {contract_id} and deleted open order {order_doc_ref.id}.")

class TradeReconciliation(Intent):

    async def _core(self):
        """
        Asynchronously fetches fills and reconciles them against open orders
        using atomic Firestore transactions.
        """
        self._env.logging.info('Running async trade reconciliation...')
        
        # Assumes ibgw connection is ready
        fills = await self._env.ibgw.reqFillsAsync()
        
        if not fills:
            self._env.logging.info('No new fills to reconcile.')
            return {}

        reconciliation_tasks = [self._reconcile_one_fill(fill) for fill in fills]
        processed_fills = await asyncio.gather(*reconciliation_tasks)
        
        final_fills = [f for f in processed_fills if f]
        self._activity_log.update(fills=final_fills)
        self._env.logging.info(f'Successfully processed {len(final_fills)} fills.')

        return self._activity_log

    async def _reconcile_one_fill(self, fill):
        """
        Finds the corresponding open order for a single fill and triggers
        the transactional update.
        """
        contract_id = fill.contract.conId
        
        query = self._env.db.collection(f'positions/{self._env.trading_mode}/openOrders').where('permId', '==', fill.execution.permId)
        docs = [doc async for doc in query.stream()]

        if not docs:
            logging.warning(f"Could not find open order for fill with permId {fill.execution.permId}. It might have been reconciled already.")
            return None

        order_doc_ref = docs[0].reference
        order_data = docs[0].to_dict()

        for strategy, quantity_in_order in order_data.get('source', {}).items():
            holdings_doc_ref = self._env.db.document(f'positions/{self._env.trading_mode}/holdings/{strategy}')
            
            try:
                await _update_holdings_and_remove_open_order_async(self._env.db.transaction(), holdings_doc_ref, order_doc_ref, contract_id, quantity_in_order)
                logging.info(f"Reconciled fill for strategy {strategy}: {quantity_in_order} of conId {contract_id}")
            except Exception as e:
                logging.error(f"Error during transactional update for permId {fill.execution.permId}: {e}", exc_info=True)
                return None
        
        return fill.execution.nonDefaults()