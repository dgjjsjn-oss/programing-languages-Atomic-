def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

sum_v = 0
for i in range(1, 20000001):
    sum_v += i

arr = [i * 2 for i in range(1000000)]
asum = sum(arr)

print(fib(27))
print(sum_v)
print(asum)
