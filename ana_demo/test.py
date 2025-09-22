import asyncio
from analysts.fundamentals import get_fundamentals_func

async def main():
    result = await get_fundamentals_func("AAPL")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
