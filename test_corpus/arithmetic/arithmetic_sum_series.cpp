// arithmetic_sum_series: long long accumulation of series sums.
// Iterative sums equal closed forms; both are printed for cross-checking.
// 1..N sums stay far below 2^63 so no overflow occurs.
#include <cstdio>

int main() {
    const int n = 100000;

    long long sum = 0;
    for (int i = 1; i <= n; ++i) {
        sum += i;
    }

    long long sum_squares = 0;
    for (int i = 1; i <= 1000; ++i) {
        sum_squares += static_cast<long long>(i) * i;
    }

    const long long sum_formula = static_cast<long long>(n) * (n + 1) / 2;
    const long long square_formula = 1000LL * 1001 * 2001 / 6;

    std::printf("%lld\n", sum);              // 5000050000
    std::printf("%lld\n", sum_formula);      // 5000050000
    std::printf("%lld\n", sum_squares);      // 333833500
    std::printf("%lld\n", square_formula);   // 333833500
    std::printf("%d\n", sum == sum_formula && sum_squares == square_formula ? 1 : 0);
    return 0;
}
