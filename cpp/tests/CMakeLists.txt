# Native C++ tests linking the compreg_core library target defined by ../CMakeLists.txt.
enable_testing()

add_executable(test_bench_kernels test_bench_kernels.cpp)
target_link_libraries(test_bench_kernels PRIVATE compreg_core)
add_test(NAME cpp_bench_kernels COMMAND test_bench_kernels)

add_executable(test_assertions test_assertions.cpp)
target_link_libraries(test_assertions PRIVATE compreg_core)
add_test(NAME cpp_assertions_selftest COMMAND test_assertions)

# Optional: run the Python unit/integration tests through CTest as well, so a
# single `ctest` invocation executes the meaningful test surface.
set(COMPREG_ENABLE_PYTHON_TESTS ON CACHE BOOL "Register pytest via CTest")
if(COMPREG_ENABLE_PYTHON_TESTS)
    find_package(Python3 QUIET COMPONENTS Interpreter)
    if(Python3_Interpreter_FOUND)
        # Require pytest importable by that interpreter; otherwise skip
        # registration with a status message (never a silent drop).
        execute_process(
            COMMAND "${Python3_EXECUTABLE}" -m pytest --version
            RESULT_VARIABLE pytest_probe
            OUTPUT_QUIET ERROR_QUIET
        )
        if(pytest_probe EQUAL 0)
            # Only the unit suite is registered: integration tests build/run
            # CMake themselves and running them through `ctest` would recurse.
            add_test(NAME python_unit_tests
                     COMMAND "${Python3_EXECUTABLE}" -m pytest
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/unit" -q)
        else()
            message(STATUS "compreg: pytest not importable by ${Python3_EXECUTABLE}; python tests not registered with CTest")
        endif()
    else()
        message(STATUS "compreg: Python interpreter not found; python tests not registered with CTest")
    endif()
endif()
