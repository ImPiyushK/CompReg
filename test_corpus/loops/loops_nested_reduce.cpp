// loops_nested_reduce: 1D convolution with two distinct length-3 kernels
// plus a windowed correlate channel. Signals are bounded 0..100 and the
// products stay far below 2^63, so the int64 accumulation is well defined.
#include <cstdio>

int main() {
    constexpr int n = 64;
    constexpr int kk = 3;
    constexpr int channels = 3;  // two conv kernels + one correlate channel

    long long signal[n];
    const int kernels[2][kk] = {{1, -2, 2}, {2, 1, -1}};

    for (int i = 0; i < n; ++i) {
        signal[i] = (37 * i + 11) % 101;  // deterministic 0..100 ladder
    }

    long long outputs[channels];
    long long accumulator = 0;

    for (int c = 0; c < channels; ++c) {
        long long total = 0;
        for (int i = 0; i <= n - kk; ++i) {
            if (c < 2) {
                long long term = 0;
                for (int j = 0; j < kk; ++j) {
                    term += signal[i + j] * kernels[c][j];
                }
                total += term;
            } else {
                // Correlate: reversed kernel dot product for kernel 0.
                long long term = 0;
                for (int j = 0; j < kk; ++j) {
                    term += signal[i + j] * kernels[0][kk - 1 - j];
                }
                total += term;
            }
        }
        outputs[c] = total;
        accumulator += total;
    }

    for (int c = 0; c < channels; ++c) {
        std::printf("%lld\n", outputs[c]);
    }
    std::printf("%lld\n", accumulator);
    return 0;
}
