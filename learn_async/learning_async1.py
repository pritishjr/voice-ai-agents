
import asyncio
import time

def sync_function(input_str: str) -> str:
    print("this is synchronous.")
    
    #lets the compiler know that this should last for only 0.2 seconds
    time.sleep(0.2)
    
    output = f"synchronous result: {input_str}"
    return output

#THIS IS CALLED A COROUTINE (scheduled as tasks)
async def async_function(input_str: str) -> str:
    print("this is asynchronous.")
    
    await asyncio.sleep(0.2) 
    #await function only comes under the async keyword.
    
    output = f"asychronous result: {input_str}"
    return output

#defining the main function to be ascynchronous:
async def main():
    '''
    #synchronous function
    # test_result_sync = sync_function("Test is Synchronous")
    # print(test_result_sync)
    '''
    
    '''
    #asynchronous functions/coroutines:
    test_coroutine_object = async_function("Test")
    print(test_coroutine_object) #coroutine object
    
    #to run the coroutine object we must await it:
    test_coroutine_result = await test_coroutine_object
    print(test_coroutine_result)
    '''
    
    #TASKS: we can assign tasks in the event loop that can be scheduled to be executed independently whenever it gets control.
    '''
    test_obj = async_function("TEST")
    task = asyncio.create_task(test_obj)
    print(task)
    
    task_result = await task
    print(task_result)
    '''
    
    
    
if __name__ == "__main__":

#this is how to run an event loop (manages asynchronous functions)
# here our event loop is the main function itself which is asynchronous.
    asyncio.run(main())
    
    