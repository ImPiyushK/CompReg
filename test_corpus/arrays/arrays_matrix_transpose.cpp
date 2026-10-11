// arrays_matrix_transpose: transpose a fixed 3x4 matrix.
#include <cstdio>

int main() {
    constexpr int rows = 3;
    constexpr int cols = 4;
    int matrix[rows][cols];

    for (int i = 0; i < rows; ++i) {
        for (int j = 0; j < cols; ++j) {
            matrix[i][j] = 10 * i + j;
        }
    }

    for (int j = 0; j < cols; ++j) {
        for (int i = 0; i < rows; ++i) {
            std::printf("%d ", matrix[i][j]);
        }
        std::printf("\n");
    }
    return 0;
}
