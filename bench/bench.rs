fn fib(n: i64) -> i64 {
    if n < 2 { return n; }
    fib(n - 1) + fib(n - 2)
}

fn main() {
    let mut sum: i64 = 0;
    let mut i: i64 = 1;
    while i <= 20_000_000 { sum += i; i += 1; }
    let mut arr: Vec<i64> = vec![0; 1_000_000];
    for j in 0..1_000_000usize { arr[j] = (j as i64) * 2; }
    let mut asum: i64 = 0;
    for v in arr.iter() { asum += *v; }
    println!("{}", fib(27));
    println!("{}", sum);
    println!("{}", asum);
}
