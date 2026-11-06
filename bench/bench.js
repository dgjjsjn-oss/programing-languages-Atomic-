function fib(n) {
  if (n < 2) return n;
  return fib(n - 1) + fib(n - 2);
}
let sum = 0;
for (let i = 1; i <= 20000000; i++) sum += i;
const arr = new Array(1000000);
for (let i = 0; i < 1000000; i++) arr[i] = i * 2;
let asum = 0;
for (let i = 0; i < 1000000; i++) asum += arr[i];
console.log(fib(27));
console.log(sum);
console.log(asum);
