namespace Jidota;

/// <summary>
/// The Claude Code plugin (Factory/: agents and skills) packaged with the tool, in plugin/ next to
/// the binaries. Agent files are read from here to build the instructions of every claude -p run
/// (ARCHITECTURE.md §4 "One agent run"); jidota never edits them.
/// </summary>
internal static class Plugin
{
    public static string Folder => Path.Combine(AppContext.BaseDirectory, "plugin");

    public static string AgentFile(string agent) => Path.Combine(Folder, "agents", agent + ".md");
}
