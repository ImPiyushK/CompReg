// recursion_fib_memo: recursive Fibonacci with a memo table.
#include <cstdio>

constexpr int kMaxN = 64;
static long long memo[kMaxN];

static long long fib(int n) {
    if (n < 2) {
        return n;
    }
    if (memo[n] != 0) {
        return memo[n];
    }
    memo[n] = fib(n - 1) + fib(n - 2);
    return memo[n];
}

int main() {
    for (int i = 0; i <= 12; ++i) {
        std::printf("%lld ", fib(i));
    }
    std::printf("\n");
    std::printf("%lld\n", fib(20));    // 6765
    std::printf("%lld\n", fib(40));    // 102334155
    std::printf("%lld\n", fib(50));    // 12586269025
    return 0;
}
