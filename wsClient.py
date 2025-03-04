import asyncio
import websockets

async def ws_client():
    uri = "ws://localhost:8003/ws"
    async with websockets.connect(uri) as websocket:
        # Mengirim pesan ke server (opsional)
        await websocket.send("Halo dari client Python!")
        print("Pesan terkirim ke server.")

        # Menerima pesan secara terus menerus dari server
        while True:
            message = await websocket.recv()
            print("Pesan diterima:", message)

if __name__ == "__main__":
    asyncio.run(ws_client())
