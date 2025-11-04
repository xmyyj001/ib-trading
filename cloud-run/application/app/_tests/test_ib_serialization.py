import unittest

from ib_insync import Order, Stock

from lib.ib_serialization import contract_to_dict, dict_to_contract, order_to_dict


class TestIbSerialization(unittest.TestCase):
    def test_order_to_dict_basic(self) -> None:
        order = Order(
            orderId=42,
            action="BUY",
            totalQuantity=5,
            orderType="LMT",
            lmtPrice=123.45,
        )

        serialized = order_to_dict(order)

        self.assertEqual(serialized["orderId"], 42)
        self.assertEqual(serialized["action"], "BUY")
        self.assertEqual(serialized["totalQuantity"], 5)
        self.assertEqual(serialized["orderType"], "LMT")
        self.assertEqual(serialized["lmtPrice"], 123.45)
        self.assertTrue(all(not key.startswith("_") for key in serialized))

    def test_order_to_dict_none(self) -> None:
        self.assertEqual(order_to_dict(None), {})

    def test_contract_round_trip(self) -> None:
        contract = Stock(symbol="AAPL", exchange="SMART", currency="USD")

        serialized = contract_to_dict(contract)
        reconstructed = dict_to_contract(serialized)

        self.assertEqual(serialized["symbol"], "AAPL")
        self.assertEqual(reconstructed.symbol, "AAPL")
        self.assertEqual(reconstructed.exchange, "SMART")
        self.assertEqual(reconstructed.currency, "USD")


if __name__ == "__main__":
    unittest.main()
