# RUN: %python -m artiq.compiler.testbench.jit %s >%t
# RUN: OutputCheck %s --file-to-check=%t
# REQUIRES: exceptions

def catch(f):
    try:
        f()
    except ZeroDivisionError as zde:
        print(zde)
    except IndexError as ie:
        print(ie)

# CHECK-L: 19(0, 0, 0)
catch(lambda: 1/0)
# CHECK-L: 10(10, 1, 0)
catch(lambda: [1.0][10])
