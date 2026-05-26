
#CONCURRENCY: yes

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor

#synchronous funtion:
def sync_func(param):
    
    print(f"Starting with: {param}", flush=True)
    
    #let this function execute for "param" seconds
    #this also drops the GIL for the next thread to continue. since this is waiting (I/OBound eg: network request) and does not use CPU
    time.sleep(param)
    
    print(f"Done with {param}", flush=True)
    return f"Result: {param}"

# asynchronous function coroutine:
async def main():
    
    #initiating via queueing two tasks in the event loop:
    ''' what does "asyncio.to_thread(<sync_function>, <sync func argument>)" do?
        wraps a synchronous function with a "future" and make it awaitable.
        it will run totally in another thread. not the current thread where the our primary coroutine is.
        
        **IMP**
        so we have here 2 threads (awaitable scheduled  tasks) out from the event loop, which means when it hits "await", it will suspend the two threads concurrently at the same time.
    '''
    
    task1 = asyncio.create_task(asyncio.to_thread(sync_func,1))
    task2 = asyncio.create_task(asyncio.to_thread(sync_func,2))
    
    #awaiting the tasks:
    result1 = await task1
    print("Thread 1 is executed.")
    
    result2 = await task2
    print("Thread 2 is executed.")
    
    #getting the Process Pool
    loop = asyncio.get_running_loop()
    
    #initiating the concurrent Process Pool Executor
    with ProcessPoolExecutor as executor: 
        
        #assigning the tasks to the executor for it to automatically assign multiple cpu cores to this multi-threaded pool:
        task1 = loop.run_in_executor(executor, sync_func, 1)
        task2 = loop.run_in_executor(executor, sync_func, 2)
        
        result1 = await task1
        print("Process 1 finished.")
        result2 = await task2
        print("Process 2 finished.")
        
    return [result1, result2]

if __name__ == "__main__":
    asyncio.run(main())
