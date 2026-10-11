// compreg bench kernels: shared, deterministic computational kernels used by
// the C++ test suite. The matrix multiply is the reference implementation for
// correctness checks; bounds and value ranges are chosen so no integer or
// floating-point overflow can occur.
#ifndef COMPREG_BENCH_KERNELS_HPP
#define COMPREG_BENCH_KERNELS_HPP

#include <cstddef>
#include <vector>

namespace compreg {

/// Fills a deterministic N x N matrix (values in [0, 97) / 7.0).
std::vector<double> generate_matrix(std::size_t n, unsigned long long salt);

/// Reference dense matrix multiply: C = A x B for row-major n x n matrices.
std::vector<double> matrix_multiply(const std::vector<double>& a,
                                    const std::vector<double>& b,
                                    std::size_t n);

/// Sum of all matrix elements (row-major order, staged accumulation).
double matrix_checksum(const std::vector<double>& m, std::size_t n);

/// Deterministic integer mixing chain used by the workload benchmarks.
/// Returns the final 64-bit state; unsigned wrap-around is well-defined.
unsigned long long mix_state(unsigned long long state, unsigned long long salt);

/// Integral workload identity guard: returns a checksum-independent tag so
/// tests can detect wrong kernel linkage.
int kernel_abi_tag() noexcept;

}  // namespace compreg

#endif  // COMPREG_BENCH_KERNELS_HPP
