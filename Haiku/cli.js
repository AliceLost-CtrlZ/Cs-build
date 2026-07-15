#!/usr/bin/env node

import chalk from 'chalk';
import inquirer from 'inquirer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TASKS_FILE = path.join(__dirname, '.standup.json');

const loadTasks = () => {
  if (fs.existsSync(TASKS_FILE)) {
    return JSON.parse(fs.readFileSync(TASKS_FILE, 'utf-8'));
  }
  return { completed: [], inProgress: [], blocked: [], tomorrow: [] };
};

const saveTasks = (tasks) => {
  fs.writeFileSync(TASKS_FILE, JSON.stringify(tasks, null, 2));
};

const displayHeader = () => {
  console.clear();
  console.log(chalk.cyan.bold('\n 🚀 Daily Standup Manager\n'));
};

const displayTasks = (tasks) => {
  console.log(chalk.green.bold('\n ✅ Completed Today:'));
  if (tasks.completed.length === 0) {
    console.log(chalk.gray('   (nothing yet)'));
  } else {
    tasks.completed.forEach((t, i) => console.log(chalk.green(`   ${i + 1}. ${t}`)));
  }

  console.log(chalk.yellow.bold('\n 🔄 In Progress:'));
  if (tasks.inProgress.length === 0) {
    console.log(chalk.gray('   (nothing yet)'));
  } else {
    tasks.inProgress.forEach((t, i) => console.log(chalk.yellow(`   ${i + 1}. ${t}`)));
  }

  console.log(chalk.red.bold('\n 🚫 Blocked:'));
  if (tasks.blocked.length === 0) {
    console.log(chalk.gray('   (nothing yet)'));
  } else {
    tasks.blocked.forEach((t, i) => console.log(chalk.red(`   ${i + 1}. ${t}`)));
  }

  console.log(chalk.blue.bold('\n 📅 Tomorrow:'));
  if (tasks.tomorrow.length === 0) {
    console.log(chalk.gray('   (nothing yet)'));
  } else {
    tasks.tomorrow.forEach((t, i) => console.log(chalk.blue(`   ${i + 1}. ${t}`)));
  }
};

const generateStandup = (tasks) => {
  const date = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
  console.log(chalk.cyan.bold(`\n📋 Standup Report - ${date}\n`));

  if (tasks.completed.length > 0) {
    console.log(chalk.green('Completed:'));
    tasks.completed.forEach(t => console.log(chalk.green(`  • ${t}`)));
  }

  if (tasks.inProgress.length > 0) {
    console.log(chalk.yellow('\nWorking on:'));
    tasks.inProgress.forEach(t => console.log(chalk.yellow(`  • ${t}`)));
  }

  if (tasks.blocked.length > 0) {
    console.log(chalk.red('\nBlocked by:'));
    tasks.blocked.forEach(t => console.log(chalk.red(`  • ${t}`)));
  }

  if (tasks.tomorrow.length > 0) {
    console.log(chalk.blue('\nPlanned for tomorrow:'));
    tasks.tomorrow.forEach(t => console.log(chalk.blue(`  • ${t}`)));
  }
};

const addTask = async (tasks) => {
  const { category, task } = await inquirer.prompt([
    {
      type: 'list',
      name: 'category',
      message: 'Category:',
      choices: ['✅ Completed', '🔄 In Progress', '🚫 Blocked', '📅 Tomorrow'],
    },
    {
      type: 'input',
      name: 'task',
      message: 'Task description:',
      validate: (input) => input.length > 0 || 'Please enter a task',
    },
  ]);

  const categoryMap = {
    '✅ Completed': 'completed',
    '🔄 In Progress': 'inProgress',
    '🚫 Blocked': 'blocked',
    '📅 Tomorrow': 'tomorrow',
  };

  tasks[categoryMap[category]].push(task);
  saveTasks(tasks);
  console.log(chalk.green('✓ Task added!'));
};

const editTasks = async (tasks) => {
  const categories = [
    { name: '✅ Completed', value: 'completed' },
    { name: '🔄 In Progress', value: 'inProgress' },
    { name: '🚫 Blocked', value: 'blocked' },
    { name: '📅 Tomorrow', value: 'tomorrow' },
  ];

  const { category } = await inquirer.prompt([
    {
      type: 'list',
      name: 'category',
      message: 'Edit which category?',
      choices: categories,
    },
  ]);

  if (tasks[category].length === 0) {
    console.log(chalk.yellow('No tasks in this category'));
    return;
  }

  const choices = [
    ...tasks[category].map((t, i) => ({ name: t, value: i })),
    { name: chalk.red('Delete all'), value: 'delete-all' },
  ];

  const { taskIndex } = await inquirer.prompt([
    {
      type: 'list',
      name: 'taskIndex',
      message: 'Select task to delete:',
      choices,
    },
  ]);

  if (taskIndex === 'delete-all') {
    tasks[category] = [];
  } else {
    tasks[category].splice(taskIndex, 1);
  }

  saveTasks(tasks);
  console.log(chalk.green('✓ Updated!'));
};

const main = async () => {
  displayHeader();
  const tasks = loadTasks();
  displayTasks(tasks);

  const { action } = await inquirer.prompt([
    {
      type: 'list',
      name: 'action',
      message: '\nWhat would you like to do?',
      choices: [
        { name: '➕ Add a task', value: 'add' },
        { name: '✏️  Edit tasks', value: 'edit' },
        { name: '📋 Generate standup', value: 'standup' },
        { name: '🔄 Clear all tasks (reset)', value: 'clear' },
        { name: '❌ Exit', value: 'exit' },
      ],
    },
  ]);

  switch (action) {
    case 'add':
      await addTask(tasks);
      break;
    case 'edit':
      await editTasks(tasks);
      break;
    case 'standup':
      generateStandup(tasks);
      break;
    case 'clear':
      const { confirm } = await inquirer.prompt([
        { type: 'confirm', name: 'confirm', message: 'Clear all tasks?', default: false },
      ]);
      if (confirm) {
        saveTasks({ completed: [], inProgress: [], blocked: [], tomorrow: [] });
        console.log(chalk.green('✓ All tasks cleared!'));
      }
      break;
    case 'exit':
      console.log(chalk.cyan('\n👋 Goodbye!\n'));
      process.exit(0);
  }

  // Loop back
  setTimeout(() => main(), 500);
};

main().catch(console.error);
