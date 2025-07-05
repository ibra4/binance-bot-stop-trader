import os
import time
import math
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *

# Load API keys from .env
load_dotenv()
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')

client = Client(API_KEY, API_SECRET)

SYMBOL = 'ZROUSDT'
STOP_PRICE = 1.736
LIMIT_PRICE = 1.733

TP_LEVELS = [
    {"trigger": 1.830, "trail_percent": 0.02, "portion": 0.33},
    {"trigger": 1.858, "trail_percent": 0.02, "portion": 0.33},
    {"trigger": 1.886, "trail_percent": 0.02, "portion": 0.33}
]


def get_quantity():
    balance = client.get_asset_balance(asset='ZRO')
    if balance:
        return float(balance['free'])
    return 0.0


def round_step_size(quantity, step_size):
    return math.floor(quantity / step_size) * step_size


def get_step_size(symbol):
    info = client.get_symbol_info(symbol)
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            return float(f['stepSize'])
    return 0.01


def place_stop_limit(quantity):
    print(
        f"🛑 Placing STOP LIMIT: Stop {STOP_PRICE}, Limit {LIMIT_PRICE}, Quantity {quantity}")
    client.create_order(
        symbol=SYMBOL,
        side=SIDE_SELL,
        type=ORDER_TYPE_STOP_LOSS_LIMIT,
        quantity=quantity,
        price=f"{LIMIT_PRICE:.3f}",
        stopPrice=f"{STOP_PRICE:.3f}",
        timeInForce=TIME_IN_FORCE_GTC
    )


def place_trailing_stop(entry_price, quantity, trail_percent):
    trail_value = entry_price * trail_percent
    print(
        f"🎯 Placing Trailing Stop at {entry_price:.3f} with trail {trail_value:.3f} for qty {quantity}")
    client.create_order(
        symbol=SYMBOL,
        side=SIDE_SELL,
        type="TRAILING_STOP_MARKET",
        quantity=quantity,
        priceProtect=True,
        trailingDelta=int(trail_value * 10000)  # basis points
    )


def cancel_open_stop_orders(symbol):
    orders = client.get_open_orders(symbol=symbol)
    for order in orders:
        if order['type'] == 'STOP_LOSS_LIMIT':
            print(f"❌ Cancelling STOP LIMIT order ID: {order['orderId']}")
            client.cancel_order(symbol=symbol, orderId=order['orderId'])


def get_current_orders_for_symbol(symbol):
    try:
        orders = client.get_open_orders(symbol=symbol)
        return orders
    except Exception as e:
        print(f"🔥 Error fetching open orders for {symbol}: {e}")
        return []


def monitor_and_trade():
    print("🚀 Monitoring price for triggers...")
    executed_trails = set()
    step = get_step_size(SYMBOL)
    full_qty = round_step_size(get_quantity(), step)
    print(f"📦 Available ZRO: {full_qty} at step size {step}")

    if full_qty == 0:
        print("⚠️ No ZRO available!")
        return

    # Place initial Stop-Limit for full quantity
    place_stop_limit(full_qty)

    while True:
        try:
            price = float(client.get_symbol_ticker(symbol=SYMBOL)['price'])

            for i, TP in enumerate(TP_LEVELS):
                if i in executed_trails:
                    continue
                if price >= TP['trigger']:
                    print(f"\n🎯 TP{i+1} triggered! Price: {price:.3f}")

                    # Cancel current stop-limit to free up funds
                    cancel_open_stop_orders(SYMBOL)
                    time.sleep(1)

                    # Recalculate fresh available balance
                    total_qty = round_step_size(get_quantity(), step)
                    if total_qty == 0:
                        print("⚠️ No available ZRO to place trailing stop.")
                        return

                    # Split the portion
                    tp_qty = round_step_size(total_qty * TP['portion'], step)
                    place_trailing_stop(price, tp_qty, TP['trail_percent'])
                    executed_trails.add(i)

                    # Recalculate remaining and re-place stop-limit
                    remaining_qty = round_step_size(get_quantity(), step)
                    if remaining_qty > 0:
                        place_stop_limit(remaining_qty)
                    break

            time.sleep(5)
        except Exception as e:
            print("🔥 Error:", e)
            time.sleep(10)


if __name__ == "__main__":
    orders = get_current_orders_for_symbol(SYMBOL)
    if orders:
        print(f"Found {len(orders)} open orders for {SYMBOL}. Cancelling them.")
        for order in orders:
            client.cancel_order(symbol=SYMBOL, orderId=order['orderId'])
    else:
        print(f"No open orders for {SYMBOL}. Proceeding with trading.")
    monitor_and_trade()
