import os

def main():
    os.fork()  # First fork
    os.fork()  # Second fork
    os.fork()  # Third fork
    print("hello")

if __name__ == "__main__":
    main()
