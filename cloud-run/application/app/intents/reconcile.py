from intents.intent import Intent

class Reconcile(Intent):
    def _core(self):
        self._env.logging.warning("Starting manual reconciliation...")
        ib_positions = self._env.ibgw.reqPositions()
        broker_portfolio = {str(p.contract.conId): p.position for p in ib_positions}
        holdings_ref = self._env.db.collection(f'positions/{self._env.trading_mode}/holdings')
        for doc in list(holdings_ref.stream()):
            doc.reference.delete()
        if broker_portfolio:
            recon_doc_ref = holdings_ref.document('reconciled_holdings')
            recon_doc_ref.set(broker_portfolio)
        result = {"status": "Reconciliation complete", "reconciledPortfolio": broker_portfolio}
        self._activity_log.update(**result)
        return result
