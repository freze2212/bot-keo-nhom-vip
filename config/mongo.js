const mongoose = require("mongoose");
mongoose.set("strictQuery", true);
require("dotenv").config();

const mongoOptions = {
  maxPoolSize: 10,
  minPoolSize: 2,
  serverSelectionTimeoutMS: 15000,
  connectTimeoutMS: 15000,
  socketTimeoutMS: 45000,
  retryWrites: true,
};

async function connect() {
  try {
    const uri = process.env.URL_CONNECT_MONGODB || "mongodb://127.0.0.1:27017/db_bacarat";
    const opts = { ...mongoOptions };
    if (uri.includes("@") && !uri.includes("authSource")) {
      opts.authSource = "admin";
    }
    await mongoose.connect(uri, opts);
    console.info("connect database db_bacarat success");
  } catch (error) {
    console.error("MongoDB connection error:", error.message);
  }
}

mongoose.connection.on("disconnected", () => {
  console.error("MongoDB disconnected — reconnect on next operation");
});

module.exports = { connect };
