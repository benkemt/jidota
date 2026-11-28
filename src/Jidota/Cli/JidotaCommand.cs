using System.CommandLine;

namespace Jidota.Cli;

/// <summary>
/// The root command `jidota`. One System.CommandLine parser for jidota and all its subcommands
/// (ARCHITECTURE.md §2.2). It has no subcommand yet: they are added by tickets 13, 32 and 36–41.
/// </summary>
internal static class JidotaCommand
{
    public const string Description =
        "jidota: the JidoTa code factory. Runs every agent as its own claude -p process, records every run, " +
        "picks up Ready tickets from the GitHub Project and serves a local dashboard.";

    public static RootCommand Create() => new(Description);
}
