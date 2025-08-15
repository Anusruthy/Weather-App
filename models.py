from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class WeatherQuery(Base):
    __tablename__ = "weather_queries"

    id = Column(Integer, primary_key=True)
    location_name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    weather_data = relationship("WeatherData", back_populates="query", cascade="all, delete-orphan")

class WeatherData(Base):
    __tablename__ = "weather_data"

    id = Column(Integer, primary_key=True)
    query_id = Column(Integer, ForeignKey("weather_queries.id"))
    date = Column(Date, nullable=False)
    temp = Column(Float, nullable=False)
    description = Column(String, nullable=False)

    query = relationship("WeatherQuery", back_populates="weather_data")
