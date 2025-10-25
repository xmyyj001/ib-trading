import asyncio
from intents.intent import Intent
import logging

class TradeReconciliation(Intent):
    """
    An intent that performs a full reconciliation of portfolio positions and also
    audits recent fills against the activity log.
    Its primary responsibility is to ensure Firestore reflects the ground truth.
    """

    async def _core_async(self):
        self._env.logging.info('--- Starting Full Portfolio Reconciliation & Audit ---')

        # --- Step 1: Perform Authoritative Portfolio Snapshot ---
        # This is the primary function and must always run.
        try:
            # CORRECTED: portfolio() is a sync method that returns the cached portfolio.
            portfolio = self._env.ibgw.portfolio()
            self._env.logging.info(f"Fetched {len(portfolio)} items from portfolio.")

            holdings_snapshot = {str(item.contract.conId): item.position for item in portfolio}
            self._env.logging.info(f"Constructed holdings snapshot: {holdings_snapshot}")

            holdings_doc_ref = self._env.db.document(f'positions/{self._env.trading_mode}/holdings/all_positions')
            # CORRECTED: .set() is a synchronous method.
            holdings_doc_ref.set(holdings_snapshot, merge=False)
            self._env.logging.info(f"Successfully wrote portfolio snapshot to {holdings_doc_ref.path}")
            self._activity_log.update(reconciled_holdings=holdings_snapshot)

        except Exception as e:
            self._env.logging.error(f"CRITICAL: Failed to perform portfolio snapshot: {e}", exc_info=True)
            # We re-raise to make it clear that the core reconciliation failed.
            raise e

        # --- Step 2: Audit Recent Fills (Secondary Function) ---
        self._env.logging.info('--- Auditing recent fills against activity log ---')
        fills = await self._env.ibgw.reqExecutionsAsync()
        if not fills:
            self._env.logging.info('No new fills to audit.')
            return self._activity_log # Still a success if snapshot was written

        self._env.logging.info(f"Found {len(fills)} fills to process for audit.")

        fills_by_permid = {}
        for fill in fills:
            perm_id = str(fill.execution.permId)
            if perm_id not in fills_by_permid:
                fills_by_permid[perm_id] = []
            fills_by_permid[perm_id].append(fill)

        reconciliation_tasks = [
            self._reconcile_one_order(perm_id, order_fills)
            for perm_id, order_fills in fills_by_permid.items()
        ]
        
        results = await asyncio.gather(*reconciliation_tasks)
        
        processed_orders = [res for res in results if res]
        self._activity_log.update(audited_orders=processed_orders)
        self._env.logging.info(f'Successfully audited {len(processed_orders)} orders.')

        return self._activity_log

    async def _reconcile_one_order(self, perm_id, fills):
        """Finds the corresponding activity log for an order and updates it with fill details."""
        # This sub-function remains the same as it correctly handles the audit part.
        activity_query = self._env.db.collection('activity').where(
            'orders.permId', '==', perm_id
        ).limit(1)
        
        docs = [doc async for doc in activity_query.stream()]

        if not docs:
            logging.warning(f"Audit: Could not find activity log for order with permId {perm_id}.")
            return None

        activity_doc_ref = docs[0].reference
        activity_data = docs[0].to_dict()
        
        total_filled_qty = sum(f.execution.shares for f in fills)
        avg_fill_price = sum(f.execution.shares * f.execution.price for f in fills) / total_filled_qty
        
        order_to_update = next((o for o in activity_data.get('orders', []) if o.get('permId') == perm_id), None)

        if not order_to_update:
             logging.error(f"Audit: Found activity {activity_doc_ref.id} but couldn't find order with permId {perm_id}.")
             return None

        order_to_update['status'] = 'Filled'
        order_to_update['avgFillPrice'] = avg_fill_price
        order_to_update['filledQuantity'] = total_filled_qty
        order_to_update['lastUpdateTime'] = datetime.utcnow().isoformat()

        try:
            await activity_doc_ref.update({'orders': activity_data['orders']})
            logging.info(f"Audit success: Updated activity {activity_doc_ref.id} for order {perm_id}.")
            return perm_id
        except Exception as e:
            logging.error(f"Audit fail: Could not update activity log for permId {perm_id}: {e}", exc_info=True)
            return None