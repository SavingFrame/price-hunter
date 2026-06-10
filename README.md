# Cjenolovac (Price Hunter)

Cjenolovac ("price hunter" in Croatian) is an application for collecting grocery prices from Croatian shops and comparing them across stores.

The goal is to make it easy to maintain a list of products, track their prices in different shops, and understand where a grocery basket is cheaper.

## What this project does

- Parses grocery product prices from Croatian shops.
- Stores products with normalized names, categories, units, and shop-specific prices.
- Compares the same or similar products across multiple shops.
- Shows price history and price charts over time.
- Helps users build a grocery list and estimate the cheapest place to buy it.

## Main use case

A user creates a list of products, for example milk, eggs, bread, rice, and coffee. The app compares available prices for those products in different Croatian shops and shows:

- which shop has the lowest price per product
- how prices changed over time
- the total basket price per shop
- where the full basket is cheapest

## Future idea

Later, the app should support uploading a grocery bill from a previous shopping trip. The app would parse the receipt, detect the purchased products, and compare how much the same basket would cost in other shops.

Example:

1. Upload last week’s grocery bill.
2. Extract products, quantities, and prices.
3. Match the products with current shop prices.
4. Show where the same basket is cheaper today.

## Tech stack

This project is based on a full stack setup:

- Backend: FastAPI, SQLModel, SQLite
- Frontend: React, TypeScript, Vite
- Local development: Docker Compose

## Development

Backend docs: [backend/README.md](./backend/README.md)

Frontend docs: [frontend/README.md](./frontend/README.md)

General development docs: [development.md](./development.md)

Deployment docs: [deployment.md](./deployment.md)

## Status

Early development. The product direction is focused on grocery price parsing, comparison, basket optimization, and future receipt upload support.
