cmake_minimum_required(VERSION 3.20)
project(CompReg VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(COMPREG_BUILD_TESTS "Build CompReg native tests" ON)
option(COMPREG_ENABLE_PYTHON_TESTS "Register Python pytest tests with CTest" ON)

# CTestConfig.cmake carries the project description for CDash-style tools.
include("${CMAKE_CURRENT_SOURCE_DIR}/CTestConfig.cmake")

include(CTest)

add_subdirectory(cpp)
