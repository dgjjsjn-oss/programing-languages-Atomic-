public class Bench {
    static long fib(long n) {
        if (n < 2) return n;
        return fib(n - 1) + fib(n - 2);
    }
    public static void main(String[] args) {
        long sum = 0;
        for (long i = 1; i <= 20000000L; i++) sum += i;
        long[] arr = new long[1000000];
        for (int i = 0; i < 1000000; i++) arr[i] = ((long) i) * 2;
        long asum = 0;
        for (int i = 0; i < 1000000; i++) asum += arr[i];
        System.out.println(fib(27));
        System.out.println(sum);
        System.out.println(asum);
    }
}
