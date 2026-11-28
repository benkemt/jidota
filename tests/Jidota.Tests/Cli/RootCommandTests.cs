using System.CommandLine;
using Jidota.Cli;

namespace Jidota.Tests.Cli;

[Trait("Category", "Unit")]
public class RootCommandTests
{
    [Fact]
    public void Help_exits_0_and_names_jidota()
    {
        var output = new StringWriter();
        var configuration = new InvocationConfiguration { Output = output, Error = new StringWriter() };

        var exit = JidotaCommand.Create().Parse(["--help"]).Invoke(configuration);

        Assert.Equal(0, exit);
        Assert.Contains("jidota", output.ToString());
    }
}
