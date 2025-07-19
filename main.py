import asyncio

async def run_bot(path):
    proc = await asyncio.create_subprocess_exec('python3', path)
    await proc.wait()

async def main():
    await asyncio.gather(
        run_bot("nottherealepic.py"),
        run_bot("epicgiveaway.py"),
        run_bot("pinger.py")
    )

asyncio.run(main())
