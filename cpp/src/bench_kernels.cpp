// Reference kernels shared between C++ unit tests and documentation
// examples. Matrix values are bounded so products and sums stay exact in
// double arithmetic.
#include "compreg/bench_kernels.hpp"

#include <cmath>

namespace compreg {

std::vector<double> generate_matrix(std::size_t n, unsigned long long salt) {
    std::vector<double> matrix(n * n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) {
            const unsigned long long value =
                ((i * 7ULL + j * 3ULL + salt) % 97ULL);
            matrix[i * n + j] = static_cast<double>(value) / 7.0;
        }
    }
    return matrix;
}

std::vector<double> matrix_multiply(const std::vector<double>& a,
                                    const std::vector<double>& b,
                                    std::size_t n) {
    std::vector<double> c(n * n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t k = 0; k < n; ++k) {
            const double a_ik = a[i * n + k];
            for (std::size_t j = 0; j < n; ++j) {
                c[i * n + j] += a_ik * b[k * n + j];
            }
        }
    }
    return c;
}

double matrix_checksum(const std::vector<double>& m, std::size_t n) {
    double stage = 0.0;
    double total = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        stage = 0.0;
        for (std::size_t j = 0; j < n; ++j) {
            stage += m[i * n + j];
        }
        total += stage;
    }
    return total;
}

unsigned long long mix_state(unsigned long long state, unsigned long long salt) {
    state ^= salt;
    state *= 1103515245ULL;
    state += 12345ULL;
    state ^= state >> 33;
    state *= 0xFF51AFD7ED558CCDULL;
    state ^= state >> 33;
    return state;
}

int kernel_abi_tag() noexcept {
    return 10701;
}

}  // namespace compreg
