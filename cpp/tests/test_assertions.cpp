// Harness self-test: verifies that the assertion registry actually executes
// cases and returns correct exit codes (guards against a vacuous test suite).
#include "compreg/testing/assertions.hpp"

#include <cstdlib>

COMPREG_CASE("checks pass on true conditions") {
    CHECK(true);
    CHECK(1 + 1 == 2);
    CHECK_EQ(3 * 3, 9);
}

int main() {
    const int failures = compreg::testing::Registry::instance().run_all();
    if (failures != 0) {
        return 1;
    }
    // Also verify the harness fails correctly for a false condition by
    // running an isolated case body manually.
    compreg::testing::CaseResult probe;
    probe.ok = true;
    const bool caught_silently = compreg::testing::report(probe, false, "probe", 1, "false", "selftest");
    const bool probe_failed = !probe.ok && !caught_silently;
    if (!probe_failed) {
        std::printf("harness self-test failed: false CHECK did not produce a failure record\n");
        return 2;
    }
    std::printf("harness self-test ok\n");
    return 0;
}
