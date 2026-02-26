## ADDED Requirements

### Requirement: Assistant text messages render as Markdown
The system SHALL render assistant message content as Markdown when the message is plain text (not an HTML form and not a "saving" status message).

#### Scenario: Markdown syntax is displayed correctly
- **WHEN** assistant message contains Markdown syntax (e.g. `**bold**`, `- list`, `# heading`, `` `code` ``)
- **THEN** the client SHALL display the rendered output (bold text, bullet list, heading, inline code) instead of raw syntax

#### Scenario: Form messages are not parsed as Markdown
- **WHEN** assistant message contains `<form` (login or register form)
- **THEN** the client SHALL render the message as HTML via existing form rendering path
- **AND** the client SHALL NOT parse form content as Markdown

#### Scenario: Saving status messages are not parsed as Markdown
- **WHEN** assistant message content matches "正在保存" pattern
- **THEN** the client SHALL display the saving indicator UI
- **AND** the client SHALL NOT parse the content as Markdown

#### Scenario: Markdown rendering during streaming
- **WHEN** assistant message is being streamed and contains partial or complete Markdown
- **THEN** the client SHALL render received content as Markdown as it arrives
- **AND** incomplete Markdown syntax SHALL be displayed without breaking the UI

### Requirement: AI prompts encourage concise Markdown output
The system SHALL instruct the AI to produce concise, well-structured replies using Markdown formatting.

#### Scenario: Intent and chat prompts include Markdown guidance
- **WHEN** AI generates intent recognition or casual chat responses
- **THEN** the system SHALL include prompt guidance to reply concisely and use Markdown (headings, lists, bold) for clarity

#### Scenario: Result analysis prompt encourages Markdown
- **WHEN** AI generates reconciliation result analysis
- **THEN** the system SHALL include prompt guidance to use Markdown for readability
- **AND** the system SHALL NOT instruct the AI to avoid Markdown format
