
#running multiple asynchronous scheduled tasks at once.
#we do this using "gather"ing the coroutines

import time
import asyncio
from concurrent.futures import ProcessPoolExecutor


async def async_func(param): 
    #async so no need to use threads in async main for this func
    await asyncio.sleep(param)
    return f"result of {param}"

#main coroutine:
async def main():
    
    task1 = asyncio.create_task(async_func(1))
    task2 = asyncio.create_task(async_func(2))
    
    result1 = await task1
    result2 = await task2
    
    print(f"RESULTS of the awaited tasks: {[result1, result2]}")
    
    '''
    METHOD 1:
    - if you want the exceptions to be returned for each scheduled tasks.
    - we gather the sub-coroutines and sub-tasks.
    - output is the list of awaited results of the tasks which have run concurrently.
    '''
    
    #Gathering coroutines:
    coroutines = [async_func(i) for i in range(1,3)]
    #awaited results for each sub-coroutine:
    results_cor = await asyncio.gather(*coroutines, return_exceptions=True)
    print(f"Coroutine results: {results_cor}")
    
    #Gathering tasks:
    tasks = [asyncio.create_task(async_func(i)) for i in range(1,3)]
    #awaited results for the sub-tasks:
    results_tasks = await asyncio.gather(*tasks, return_exceptions=True)
    print(f"Tasks results: {results_tasks}")
    
    '''
    METHOD 2: Task Group
    - if you u want the tasks to be done sequentially wherein the process halts when one of the tasks returns an exception.
    '''
    
    async with asyncio.TaskGroup() as group: #Task Manager
        
        #creating+scheduling tasks into the group:
        tasks_tg = [group.create_task(async_func(i)) for i in range(1,3)]
        #automatically awaits when the Task Manager exits.
    
    #extracting the results of the Task Group:
    results_tg = [result.result() for result in tasks_tg]
    
    print(f"Results of the Task Group: {results_tg}")
    
if __name__ == "__main__":
    asyncio.run(main())
    