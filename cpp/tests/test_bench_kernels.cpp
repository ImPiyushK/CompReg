// Native C++ unit tests for the compreg kernel library.
// Registered with CTest via add_test (see ../tests/CMakeLists.txt).
#include <cmath>

#include "compreg/bench_kernels.hpp"
#include "compreg/testing/assertions.hpp"

using compreg::generate_matrix;
using compreg::matrix_checksum;
using compreg::matrix_multiply;
using compreg::mix_state;

COMPREG_CASE("identity multiplication") {
    const std::size_t n = 4;
    std::vector<double> identity(n * n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        identity[i * n + i] = 1.0;
    }
    const std::vector<double> a = generate_matrix(n, 42);
    const std::vector<double> c = matrix_multiply(a, identity, n);
    for (std::size_t i = 0; i < n * n; ++i) {
        CHECK(c[i] == a[i]);
    }
}

COMPREG_CASE("multiply matches manual elementwise expectation") {
    // 2x2 hand-computed case:
    // a = [[1,2],[3,4]], b = [[5,6],[7,8]] -> c = [[19,22],[43,50]]
    const std::vector<double> a{1, 2, 3, 4};
    const std::vector<double> b{5, 6, 7, 8};
    const std::vector<double> c = matrix_multiply(a, b, 2);
    CHECK(c[0] == 19.0);
    CHECK(c[1] == 22.0);
    CHECK(c[2] == 43.0);
    CHECK(c[3] == 50.0);
    CHECK(matrix_checksum(c, 2) == 19.0 + 22.0 + 43.0 + 50.0);
}

COMPREG_CASE("matrix checksum is order-stable") {
    const std::size_t n = 8;
    const std::vector<double> m = generate_matrix(n, 7);
    // Row-swap invariance: permuting rows preserves the total checksum.
    std::vector<double> swapped(n * n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        const std::size_t src = (i + 1) % n;
        for (std::size_t j = 0; j < n; ++j) {
            swapped[i * n + j] = m[src * n + j];
        }
    }
    const double left = matrix_checksum(m, n);
    const double right = matrix_checksum(swapped, n);
    CHECK(left == right);
    CHECK(left > 0.0);
}

COMPREG_CASE("mix_state matches the Python reference values") {
    // Verified against the framework's independent Python model
    // (exact 2^64-wrapping integer semantics).
    unsigned long long state = 2166136261ULL;
    state = mix_state(state, 0ULL);
    CHECK(state == 12080477469638829281ULL);
    // chain of three salts
    unsigned long long chained = 2166136261ULL;
    chained = mix_state(chained, 0ULL);
    chained = mix_state(chained, 31ULL);
    chained = mix_state(chained, 62ULL);
    CHECK(chained == 3615509477685523683ULL);
}

COMPREG_CASE("abi tag links the expected library") {
    CHECK(compreg::kernel_abi_tag() == 10701);
}

int main() {
    return compreg::testing::Registry::instance().run_all();
}
