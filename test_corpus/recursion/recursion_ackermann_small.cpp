// recursion_ackermann_small: bounded-blowup recursion with verified values.
// ack(3,3)=61 keeps the recursion depth modest; larger arguments would be
// inappropriate for an automated corpus.
#include <cstdio>

static int ack(int m, int n) {
    if (m == 0) {
        return n + 1;
    }
    if (n == 0) {
        return ack(m - 1, 1);
    }
    return ack(m - 1, ack(m, n - 1));
}

int main() {
    const int cases[][2] = {{0, 3}, {1, 3}, {2, 3}, {2, 5}, {3, 3}};
    for (const auto &c : cases) {
        std::printf("%d,%d=%d\n", c[0], c[1], ack(c[0], c[1]));
    }
    return 0;
}
