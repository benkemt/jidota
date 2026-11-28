using Jidota.Cli;

// Entry point of the jidota .NET tool. Commands are added to the root by later tickets
// (init: ticket 13, start/stop/status/…: ticket 32, spec/pr/workitems: tickets 36–41).
return JidotaCommand.Create().Parse(args).Invoke();
