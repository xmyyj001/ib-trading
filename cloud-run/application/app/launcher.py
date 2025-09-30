import uvicorn
import uvloop

# Install the uvloop event loop policy at the absolute start of the process
uvloop.install()

if __name__ == "__main__":
    # Programmatically start the Uvicorn server
    # It will now automatically use the uvloop
    uvicorn.run("main:app", host="0.0.0.0", port=8080)