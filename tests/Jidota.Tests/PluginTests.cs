namespace Jidota.Tests;

[Trait("Category", "Unit")]
public class PluginTests
{
    // The four agents of the code factory, read by jidota to build every claude -p run.
    [Theory]
    [InlineData("builder")]
    [InlineData("security-reviewer")]
    [InlineData("code-reviewer")]
    [InlineData("approver")]
    public void Plugin_folder_is_copied_to_the_output_with_the_agent_files(string agent)
    {
        Assert.True(File.Exists(Plugin.AgentFile(agent)), $"missing {Plugin.AgentFile(agent)}");
    }
}
