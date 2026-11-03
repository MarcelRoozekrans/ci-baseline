using LowCov;
using Xunit;

namespace LowCov.Tests;

public class CalculatorTests
{
    [Fact]
    public void Add_returns_sum() => Assert.Equal(5, new Calculator().Add(2, 3));

    [Fact]
    public void Subtract_returns_difference() => Assert.Equal(-1, new Calculator().Subtract(2, 3));

    [Fact]
    public void Square_returns_product() => Assert.Equal(9, new Calculator().Square(3));
}
