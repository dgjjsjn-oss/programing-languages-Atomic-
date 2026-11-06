#include <stdio.h>

static long long fib(long long n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

int main(void) {
    long long sum = 0;
    for (long long i = 1; i <= 20000000LL; i++) sum += i;
    static long long arr[1000000];
    for (long long i = 0; i < 1000000LL; i++) arr[i] = i * 2;
    long long asum = 0;
    for (long long i = 0; i < 1000000LL; i++) asum += arr[i];
    printf("%lld\n%lld\n%lld\n", fib(27), sum, asum);
    return 0;
}

