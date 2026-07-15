# Daily Standup CLI 🚀

A terminal-based tool for managing daily tasks and generating standups.

## Features

- ✅ Track completed tasks
- 🔄 Manage in-progress work
- 🚫 Log blocked items
- 📅 Plan for tomorrow
- 📋 Generate formatted standup reports
- 💾 Persistent storage (auto-saved)
- 🎨 Colorful terminal UI

## Installation

```bash
npm install
```

## Usage

```bash
npm start
```

Or if installed globally:

```bash
standup
```

## Commands

- **Add a task** — Add new tasks to any category
- **Edit tasks** — Remove or clear tasks
- **Generate standup** — Create a formatted report for your team
- **Clear all** — Reset everything
- **Exit** — Close the app

## File Format

Tasks are stored in `.standup.json` in the project directory:

```json
{
  "completed": ["Task 1", "Task 2"],
  "inProgress": ["Task 3"],
  "blocked": ["Task 4"],
  "tomorrow": ["Task 5"]
}
```

## License

MIT
