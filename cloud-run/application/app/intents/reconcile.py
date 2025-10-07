from intents.intent import Intent

class Reconcile(Intent):
    async def _core_async(self):
        self._env.logging.warning("Starting manual reconciliation...")
        ib_positions = self._env.ibgw.positions()
        broker_portfolio = {str(p.contract.conId): p.position for p in ib_positions}
        holdings_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings')
            strategy_docs = [doc async for doc in holdings_ref.stream()]
            
            # 3. Clear all existing strategy holdings
        if broker_portfolio:
            recon_doc_ref = holdings_ref.document('reconciled_holdings')
            await recon_doc_ref.set(broker_portfolio)
        result = {"status": "Reconciliation complete", "reconciledPortfolio": broker_portfolio}
        self._activity_log.update(**result)
        return result
