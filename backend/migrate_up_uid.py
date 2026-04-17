import asyncio
import aiomysql


async def migrate():
    pool = await aiomysql.create_pool(
        host="localhost", port=3306, user="root", password="Prototype5233",
        db="feinalive", autocommit=True
    )
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DESCRIBE up_videos")
            cols = await cur.fetchall()
            print("Current columns:")
            for col in cols:
                print(f"  {col}")

            await cur.execute("ALTER TABLE up_videos MODIFY COLUMN up_uid BIGINT NOT NULL")
            print("\nModified up_uid to BIGINT")

            await cur.execute("DESCRIBE up_videos")
            cols = await cur.fetchall()
            print("\nNew columns:")
            for col in cols:
                print(f"  {col}")
    pool.close()
    await pool.wait_closed()
    print("\nDone!")


asyncio.run(migrate())
