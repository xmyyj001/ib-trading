import asyncio
from intents.intent import Intent
import logging

class TradeReconciliation(Intent):
    """
    An intent that acts as a post-trade auditing and logging tool.
    It reconciles executed fills from the broker against the trade activities
    logged by strategies in the 'activity' collection.
    """

    async def _core_async(self):
        self._env.logging.info('--- Starting Post-Trade Reconciliation (Auditor) ---')

        # 1. Fetch all recent fills from the broker
        fills = await self._env.ibgw.reqFillsAsync()
        if not fills:
            self._env.logging.info('No new fills to reconcile.')
            return {"status": "No new fills."}

        self._env.logging.info(f"Found {len(fills)} fills to process.")

        # 2. Group fills by permId to handle multi-fill orders
        fills_by_permid = {}
        for fill in fills:
            perm_id = str(fill.execution.permId)
            if perm_id not in fills_by_permid:
                fills_by_permid[perm_id] = []
            fills_by_permid[perm_id].append(fill)

        # 3. Process each group of fills against the activity log
        reconciliation_tasks = [
            self._reconcile_one_order(perm_id, order_fills)
            for perm_id, order_fills in fills_by_permid.items()
        ]
        
        results = await asyncio.gather(*reconciliation_tasks)
        
        processed_orders = [res for res in results if res]
        self._activity_log.update(reconciled_orders=processed_orders)
        self._env.logging.info(f'Successfully reconciled {len(processed_orders)} orders.')

        return self._activity_log

    async def _reconcile_one_order(self, perm_id, fills):
        """
        Finds the corresponding activity log for an order and updates it with fill details.
        """
        activity_query = self._env.db.collection('activity').where(
            'orders.permId', '==', perm_id
        ).limit(1)
        
        docs = [doc async for doc in activity_query.stream()]

        if not docs:
            logging.warning(f"Could not find activity log for order with permId {perm_id}. It might be an external order.")
            return None

        activity_doc_ref = docs[0].reference
        activity_data = docs[0].to_dict()
        
        # Consolidate fill information
        total_filled_qty = sum(f.execution.shares for f in fills)
        avg_fill_price = sum(f.execution.shares * f.execution.price for f in fills) / total_filled_qty
        
        # Find the specific order in the activity log's orders list
        order_to_update = next((o for o in activity_data.get('orders', []) if o.get('permId') == perm_id), None)

        if not order_to_update:
             logging.error(f"Found activity {activity_doc_ref.id} for permId {perm_id}, but couldn't find the matching order entry inside it.")
             return None

        # Update the status and add execution details
        order_to_update['status'] = 'Filled'
        order_to_update['avgFillPrice'] = avg_fill_price
        order_to_update['filledQuantity'] = total_filled_qty
        order_to_update['lastUpdateTime'] = datetime.utcnow().isoformat()

        try:
            await activity_doc_ref.update({'orders': activity_data['orders']})
            logging.info(f"Successfully updated activity {activity_doc_ref.id} for order {perm_id} to Filled.")
            return perm_id
        except Exception as e:
            logging.error(f"Failed to update activity log for permId {perm_id}: {e}", exc_info=True)
            return None