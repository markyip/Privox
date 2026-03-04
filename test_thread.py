import concurrent.futures
print("Starting...")
def load():
    print("In thread: importing MLX whisper...")
    import mlx_whisper
    print("Success in thread!")
    return True

with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(load)
    print("Result:", future.result())
print("Done")
