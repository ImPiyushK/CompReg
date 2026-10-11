// bitwise_rotate_popcount: well-defined rotation (guarded for r == 0) plus
// manual popcount so no compiler builtins are involved.
#include <cstdio>

static unsigned rotl32(unsigned x, unsigned r) {
    r &= 31u;
    if (r == 0) {
        return x;  // shifting by 32 would be undefined; guard explicitly
    }
    return (x << r) | (x >> (32 - r));
}

static int popcount32(unsigned x) {
    int count = 0;
    while (x != 0u) {
        x &= (x - 1u);  // clears the lowest set bit (defined, unsigned)
        ++count;
    }
    return count;
}

int main() {
    const unsigned xs[] = {0u, 1u, 0xFFFFFFFFu, 0xDEADBEEFu, 0x80000000u, 0x0F0F0F0Fu};
    for (unsigned x : xs) {
        std::printf("x=%08x rot4=%08x pop=%d\n", x, rotl32(x, 4), popcount32(x));
    }
    std::printf("rot0equal=%d\n", rotl32(0xDEADBEEFu, 0) == 0xDEADBEEFu ? 1 : 0);
    return 0;
}
