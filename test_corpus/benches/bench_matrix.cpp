// bench_matrix: deterministic dense double matrix multiply.
// N and fill pattern are fixed; the checksum is validated with a tolerant
// float oracle (FP contraction may fuse a*b+c on some -march settings).
// Workload: N^3 multiply-adds (~0.3-1 s at -O0, tens of ms at -O2).
#include <cstdio>

constexpr int N = 384;
static double A[N][N];
static double B[N][N];
static double C[N][N];

int main() {
    for (int i = 0; i < N; ++i) {
        for (int j = 0; j < N; ++j) {
            A[i][j] = ((i * 3 + j * 7) % 97) / 7.0;
            B[i][j] = (((i + 13) * (j + 5)) % 89) / 6.0;
            C[i][j] = 0.0;
        }
    }

    for (int i = 0; i < N; ++i) {
        for (int k = 0; k < N; ++k) {
            const double a = A[i][k];
            for (int j = 0; j < N; ++j) {
                C[i][j] += a * B[k][j];
            }
        }
    }

    double checksum = 0.0;
    for (int i = 0; i < N; ++i) {
        for (int j = 0; j < N; ++j) {
            checksum += C[i][j];
        }
    }

    std::printf("%.9e\n", checksum);
    std::printf("%.9e\n", C[0][0]);
    std::printf("%.9e\n", C[N - 1][N - 1]);
    return 0;
}
