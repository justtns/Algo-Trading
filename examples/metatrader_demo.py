#!/usr/bin/env python3
"""
MetaTrader 5 Integration Demo

This script demonstrates how to:
1. Connect to MetaTrader 5
2. Stream live tick data and build bars
3. Send orders via the OrderRouter
4. Run a simple trading strategy

Before running:
1. Install MetaTrader 5: pip install MetaTrader5
2. Update config/config.json with your MT5 credentials
3. Ensure MT5 terminal is running (if using local connection)
"""
import asyncio
from pathlib import Path
import sys

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trader.core.config import SystemConfig
from trader.exec.metatrader import MetaTraderBroker, build_metatrader_router
from trader.data.metatrader_stream import MetaTraderLiveStreamer, stream_metatrader_ticks
from trader.data.pipeline import DataStreamer
from trader.exec.router import OrderRequest


def demo_connection():
    """Demo: Test MT5 connection and print account info."""
    print("=" * 60)
    print("MetaTrader 5 Connection Demo")
    print("=" * 60)
    
    # Load configuration
    try:
        config = SystemConfig.load("config/config.json")
    except FileNotFoundError:
        print("Error: config/config.json not found!")
        print("Please create the configuration file first.")
        return
    
    # Create broker instance
    print("\n1. Initializing MetaTrader 5 connection...")
    try:
        broker = MetaTraderBroker(
            login=config.metatrader.login,
            password=config.metatrader.password,
            server=config.metatrader.server,
            path=config.metatrader.path,
            deviation=config.metatrader.deviation,
            magic=config.metatrader.magic,
        )
        print("   ✓ Connected to MetaTrader 5")
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        return
    
    # Get account info
    mt5 = broker.mt5
    account_info = mt5.account_info()
    if account_info:
        print("\n2. Account Information:")
        print(f"   Login: {account_info.login}")
        print(f"   Server: {account_info.server}")
        print(f"   Balance: {account_info.balance}")
        print(f"   Equity: {account_info.equity}")
        print(f"   Margin: {account_info.margin}")
        print(f"   Free Margin: {account_info.margin_free}")
        print(f"   Leverage: 1:{account_info.leverage}")
    else:
        print("   ✗ Could not retrieve account info")
    
    # List available symbols
    print("\n3. Available Symbols (first 10):")
    symbols = mt5.symbols_get()
    if symbols:
        for i, symbol in enumerate(symbols[:10]):
            print(f"   {i+1}. {symbol.name} - {symbol.description}")
    else:
        print("   ✗ Could not retrieve symbols")
    
    # Get current market prices
    print("\n4. Sample Market Prices:")
    test_symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    for symbol in test_symbols:
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            print(f"   {symbol}: Bid={tick.bid:.5f}, Ask={tick.ask:.5f}, Spread={tick.ask - tick.bid:.5f}")
        else:
            print(f"   {symbol}: Not available")
    
    # Cleanup
    broker.shutdown()
    print("\n5. Connection closed.")
    print("=" * 60)


def demo_order_routing():
    """Demo: Send a test order via OrderRouter."""
    print("=" * 60)
    print("MetaTrader 5 Order Routing Demo")
    print("=" * 60)
    print("WARNING: This will send a REAL order to MetaTrader 5!")
    print("Make sure you're using a demo account.")
    
    response = input("\nContinue? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        return
    
    # Load configuration
    config = SystemConfig.load("config/config.json")
    
    # Build router with risk management
    print("\n1. Building OrderRouter with risk management...")
    router = build_metatrader_router(
        login=config.metatrader.login,
        password=config.metatrader.password,
        server=config.metatrader.server,
        path=config.metatrader.path,
        deviation=config.metatrader.deviation,
    )
    print("   ✓ Router initialized")
    
    # Create a test order request
    print("\n2. Creating test order request...")
    order = OrderRequest(
        symbol="EURUSD",
        side="BUY",
        size=0.01,  # Minimum lot size
        order_type="market",
        strategy_id="demo",
    )
    print(f"   Symbol: {order.symbol}")
    print(f"   Side: {order.side}")
    print(f"   Size: {order.size} lots")
    print(f"   Type: {order.order_type}")
    
    # Send the order
    print("\n3. Sending order...")
    try:
        result = router.send(order)
        print("   ✓ Order executed successfully!")
        print(f"   Order ticket: {result.order}")
        print(f"   Volume: {result.volume}")
        print(f"   Price: {result.price}")
    except Exception as e:
        print(f"   ✗ Order failed: {e}")
    
    print("\n4. Demo complete.")
    print("=" * 60)


async def demo_streaming():
    """Demo: Stream live tick data from MT5."""
    print("=" * 60)
    print("MetaTrader 5 Streaming Demo")
    print("=" * 60)
    
    # Load configuration
    config = SystemConfig.load("config/config.json")
    
    # Create data streamer
    print("\n1. Initializing data streamer...")
    streamer = DataStreamer()
    print("   ✓ DataStreamer ready")
    
    # Create broker
    print("\n2. Connecting to MetaTrader 5...")
    broker = MetaTraderBroker(
        login=config.metatrader.login,
        password=config.metatrader.password,
        server=config.metatrader.server,
        path=config.metatrader.path,
    )
    print("   ✓ Connected")
    
    # Create streamer
    print("\n3. Starting live stream...")
    symbols = ["EURUSD", "GBPUSD"]
    print(f"   Symbols: {', '.join(symbols)}")
    print(f"   Bar interval: {config.streaming.bar_seconds} seconds")
    
    mt_streamer = MetaTraderLiveStreamer(
        broker=broker,
        streamer=streamer,
        bar_seconds=config.streaming.bar_seconds,
        poll_interval=config.streaming.poll_interval,
        max_batch=config.streaming.max_batch,
        lookback_sec=config.streaming.lookback_sec,
    )
    
    # Stream for limited time
    print("\n4. Streaming ticks (will run for 30 seconds)...")
    print("   Press Ctrl+C to stop early")
    
    async def stream_with_timeout():
        try:
            await asyncio.wait_for(
                mt_streamer.stream_ticks_to_bars(symbols),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            print("\n   Timeout reached, stopping stream...")
            mt_streamer.stop()
    
    # Monitor bars
    bar_count = 0
    try:
        stream_task = asyncio.create_task(stream_with_timeout())
        
        while not stream_task.done():
            try:
                bar = await asyncio.wait_for(streamer.get(), timeout=1.0)
                if bar:
                    bar_count += 1
                    print(f"   Bar #{bar_count}: {bar.get('datetime')} - "
                          f"O={bar.get('open'):.5f} H={bar.get('high'):.5f} "
                          f"L={bar.get('low'):.5f} C={bar.get('close'):.5f}")
            except asyncio.TimeoutError:
                continue
        
        await stream_task
    except KeyboardInterrupt:
        print("\n   Interrupted by user")
        mt_streamer.stop()
    
    print(f"\n5. Streaming complete. Total bars received: {bar_count}")
    print("=" * 60)


def main():
    """Main entry point for demos."""
    print("\nMetaTrader 5 Integration Demos\n")
    print("1. Connection Test")
    print("2. Order Routing Demo (sends real order!)")
    print("3. Live Streaming Demo")
    print("0. Exit")
    
    choice = input("\nSelect demo (0-3): ")
    
    if choice == "1":
        demo_connection()
    elif choice == "2":
        demo_order_routing()
    elif choice == "3":
        asyncio.run(demo_streaming())
    elif choice == "0":
        print("Goodbye!")
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
