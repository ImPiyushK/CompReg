// arithmetic_int_basic: basic signed/unsigned arithmetic with defined behavior.
// Signed operations stay within range (products widened to long long);
// unsigned wrap-around is well-defined by the standard.
#include <cstdio>

int main() {
    const int a = 1234;
    const int b = 567;
    const unsigned ua = 4000000000u;
    const unsigned ub = 26u;

    std::printf("%d\n", a + b);                       // 1801
    std::printf("%d\n", a - b);                       // 667
    std::printf("%lld\n", static_cast<long long>(a) * b);  // 699678
    std::printf("%d\n", a / b);                       // 2
    std::printf("%d\n", a % b);                       // 100

    std::printf("%u\n", ua + ub);                     // 4000000026
    std::printf("%llu\n", static_cast<unsigned long long>(ua) * 2u);  // 8000000000
    std::printf("%u\n", ua % 7u);                     // 4000000000 % 7 = 3
    std::printf("%u\n", ua / 3u);                     // 1333333333
    return 0;
}
