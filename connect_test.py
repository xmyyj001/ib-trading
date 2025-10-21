import asyncio
import logging
from ib_insync import IB

async def run_connection_test():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ib = IB()
    
    # 增加超时时间，例如从默认的 10 秒增加到 30 秒
    connection_timeout = 30 

    try:
        logging.info(f"Attempting to connect to 127.0.0.1:4002 with a timeout of {connection_timeout} seconds...")
        await ib.connectAsync(host='127.0.0.1', port=4002, clientId=1, timeout=connection_timeout)
        
        if ib.isConnected():
            logging.info("--- SUCCESS: Connection established! ---")
            
            # 尝试一个简单的请求来验证通信
            logging.info("Requesting current time from server...")
            server_time = await ib.reqCurrentTimeAsync()
            logging.info(f"Server time: {server_time}")
            
            logging.info("Requesting account summary (this might time out)...")
            # 增加单个请求的超时时间
            ib.RequestTimeout = 30
            summary = await ib.reqAccountSummaryAsync()
            logging.info(f"Account summary received: {len(summary)} items.")

        else:
            logging.error("--- FAILED: Connection method finished, but not connected. ---")

    except asyncio.TimeoutError:
        logging.critical("--- FAILED: Connection timed out! ---")
        logging.critical("This confirms the TimeoutError. Try increasing the timeout further or check Gateway logs.")
    except Exception as e:
        logging.critical(f"--- FAILED: An unexpected error occurred: {e} ---", exc_info=True)
    finally:
        if ib.isConnected():
            ib.disconnect()
        logging.info("Test finished.")

if __name__ == "__main__":
    # Apply nest_asyncio to allow running asyncio within another event loop (like in some notebook environments)
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(run_connection_test())