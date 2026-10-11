// arithmetic_float_basic: IEEE double arithmetic and math functions.
// Output is parsed as a number list and compared with tolerance because
// libm rounding and printf formatting may differ slightly across platforms.
#include <cmath>
#include <cstdio>

int main() {
    const double a = 0.1;
    const double b = 0.2;

    std::printf("%.17g\n", a + b);   // 0.30000000000000004
    std::printf("%.17g\n", a * b);   // 0.020000000000000004
    std::printf("%.17g\n", a / b);   // 0.5
    std::printf("%.17g\n", std::sqrt(2.0));      // 1.41421356...
    std::printf("%.17g\n", std::sin(1.0));       // 0.841470984...
    std::printf("%.17g\n", std::cos(1.0));       // 0.540302305...

    // Deterministic series: geometric product and harmonic sum.
    double geo = 1.0;
    for (int i = 0; i < 20; ++i) {
        geo *= 0.9;
    }
    std::printf("%.17g\n", geo);     // 0.9^20

    double harmonic = 0.0;
    for (int i = 1; i <= 1000; ++i) {
        harmonic += 1.0 / static_cast<double>(i);
    }
    std::printf("%.17g\n", harmonic);  // H_1000 = 7.485470860...
    return 0;
}
