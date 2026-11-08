@domain:editor-integrations @area:editor-setup @from:extensions/vscode
Feature: Editor setup and health
  Gets a developer from a fresh editor to a working scan by finding gandalf, offering to install it, and saying what the environment lacks.

  @id:editor-integrations.editor-setup.005 @rule:editor.setup.launcher-precedence @inferred @source:extensions/vscode/src/launcher.ts#resolveLauncher
  Scenario Outline: The extension uses the most explicit gandalf it can find
    Given <available>
    When the developer starts a scan
    Then the log says gandalf is used via <used>

    Examples:
      | available                                                              | used                                           |
      | gandalf.path points at a gandalf checkout, and gandalf is also on PATH | python3 -m gandalf from that checkout          |
      | gandalf.path points at a wrapper script                                | that wrapper                                   |
      | the open workspace is a gandalf checkout, and gandalf is also on PATH  | python3 -m gandalf from the workspace checkout |
      | only gandalf on PATH                                                   | gandalf on PATH                                |
      | only a clone in ~/.local/share/gandalf                                 | python3 -m gandalf from that clone             |

  @id:editor-integrations.editor-setup.006 @rule:editor.setup.environment-check @verified @source:extensions/vscode/src/doctor.ts#runDoctor @test:extensions/vscode/src/test/doctor.test.ts#checks each thing a scan cannot report on for itself, and no tool inventory @test:extensions/vscode/src/test/doctor.test.ts#offers to build the missing image rather than explaining docker @test:extensions/vscode/src/test/doctor.test.ts#always offers the log, and it opens @test:extensions/vscode/src/test/doctor.test.ts#sends someone with no git to the official instructions, not to a package manager @test:extensions/vscode/src/test/doctor.test.ts#names the directory it judged, and calls out one that is not a repository
  Scenario: Check Environment reports what gandalf needs and offers a fix for each gap
    Given gandalf runs, git is on PATH, docker is on PATH but the gandalf-tools image is missing
    When the developer checks the environment
    Then the log lists gandalf, git, workspace, docker, scanner tools and LLM endpoint, each marked ✔ or ✖
    And a warning names the failed checks and ends "— see the log"
    And it offers "Build tools image" and "Show log"

  @id:editor-integrations.editor-setup.007 @rule:editor.setup.tools-image-from-checkout @verified @source:extensions/vscode/src/doctor.ts#buildToolsImage @test:extensions/vscode/src/test/doctor.test.ts#runs the build in a terminal, from the checkout that owns the Dockerfile @test:extensions/vscode/src/test/doctor.test.ts#explains where the image comes from rather than failing silently
  Scenario Outline: The scanner tools image can only be built from a gandalf checkout
    Given gandalf is used from <source>
    When the developer builds the tools image
    Then <outcome>

    Examples:
      | source                                 | outcome                                                                                                         |
      | a checkout containing tools.Dockerfile | a terminal "gandalf: build tools" runs "docker build -f tools.Dockerfile -t gandalf-tools ." in that checkout   |
      | a wrapper with no checkout             | an error explains the image is built from tools.Dockerfile in a gandalf checkout and to set gandalf.path to one |
