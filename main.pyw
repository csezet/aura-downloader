"""Console-free source launcher; use the same startup and shutdown as the EXE."""
import sys

if __name__ == "__main__" and "--smoke-test" in sys.argv:
    from core.smoke_check import smoke_main
    sys.exit(smoke_main(sys.argv[1:]))

from main import MainWindow, finalize_background_work, main

if __name__ == "__main__":
    main()
