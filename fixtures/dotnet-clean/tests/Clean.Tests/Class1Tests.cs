using Clean;
using Xunit;

namespace Clean.Tests;

public class Class1Tests
{
    [Fact]
    public void Add_returns_sum() => Assert.Equal(5, new Class1().Add(2, 3));

    [Fact]
    public void Greet_prefixes_name() => Assert.Equal("Hello, Ada", new Class1().Greet("Ada"));
}
