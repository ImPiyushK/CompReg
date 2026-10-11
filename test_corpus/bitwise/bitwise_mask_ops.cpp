// bitwise_mask_ops: set/clear/test bit operations on unsigned data.
// All arithmetic is unsigned; `0u - x` wrap-around is well-defined and is the
// classic two's-complement negation used for lowest-bit isolation.
#include <cstdio>

int main() {
    unsigned word = 0u;

    word |= (1u << 0);
    word |= (1u << 5);
    word |= (1u << 31);
    std::printf("after_set=%08x\n", word);

    word &= ~(1u << 5);
    std::printf("after_clear=%08x\n", word);

    const int bit0 = (word & (1u << 0)) != 0u;
    const int bit5 = (word & (1u << 5)) != 0u;
    const int bit31 = (word & (1u << 31)) != 0u;
    std::printf("bits=%d%d%d\n", bit31, bit5, bit0);

    const unsigned selectors[] = {12u, 96u, 1024u, 0xFFFFFFFFu, 0u};
    for (unsigned x : selectors) {
        // Lowest set bit: unsigned `0u - x` yields the two's complement.
        const unsigned lowest = x & (0u - x);
        // Highest set bit: scan from the top.
        unsigned highest = 0u;
        for (unsigned m = 0x80000000u; m != 0u && highest == 0u; m >>= 1) {
            highest = (x & m) != 0u ? m : 0u;
        }
        std::printf("x=%u lowest=%u highest=%u\n", x, lowest, highest);
    }
    return 0;
}
