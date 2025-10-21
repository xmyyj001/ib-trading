from intents.intent import Intent

class Reconcile(Intent):
    """
    Manually reconciles Firestore holdings with the broker's current positions.
    This is a powerful tool to fix state drift. Use with caution.
    """
    async def _core_async(self):
        self._env.logging.warning("Starting manual reconciliation...")

        # 1. Get broker positions
        ib_positions = await self._env.ibgw.reqPositionsAsync()
        broker_portfolio = {str(p.contract.conId): p.position for p in ib_positions if p.position != 0}

        # 2. Get all strategy holding documents from Firestore
        holdings_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings')
        strategy_docs = [doc for doc in holdings_ref.stream()]
        
        # 3. Clear all existing strategy holdings
        for doc in strategy_docs:
            self._env.logging.info(f"Deleting holdings for strategy: {doc.id}")
            await doc.reference.delete()

        # 4. Set the new, reconciled holdings under a special document.
        # This avoids incorrectly attributing positions to a specific strategy.
        if broker_portfolio:
            recon_doc_ref = holdings_ref.document('reconciled_holdings')
            self._env.logging.info(f"Setting reconciled holdings: {broker_portfolio}")
            await recon_doc_ref.set(broker_portfolio)

        result = {"status": "Reconciliation complete", "reconciledPortfolio": broker_portfolio}
        self._activity_log.update(**result)
        return result